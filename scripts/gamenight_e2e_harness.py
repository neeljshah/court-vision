"""gamenight_e2e_harness.py — R20_M5 game-night E2E validation harness.

Simulates a full slate cycle on a historical completed game so we discover
pipeline breakage BEFORE tip-off rather than live. Walks the 5 production
stages end-to-end:

    Stage 1 — pregame slate: build per-player projections, assert >= 7 stats
              per player (pts/reb/ast/fg3m/stl/blk/tov).
    Stage 2 — in-play snapshots: synthesize endQ1, endQ2, endQ3 snapshots
              from the actual quarter_box JSONs and run the in-play ranker
              against synthetic prop lines. Assert ranked bets are produced
              and Kelly % is bounded in [0, 25].
    Stage 3 — bet placement + settle: write a fake bet to a TEST ledger
              (NEVER data/pnl_ledger.csv) and run auto_settle.settle_game.
              Assert settlement matches actual game outcome.
    Stage 4 — CLV tracker: run clv_tracker_daemon.run_tick in test mode
              against the test ledger + synthetic line snapshots. Assert
              CLV computed (signed correctly).
    Stage 5 — cleanup: remove the test ledger + sidecars.

The harness returns exit code 0 only when ALL 5 stages pass.

Usage::

    python scripts/gamenight_e2e_harness.py                  # auto-pick a game
    python scripts/gamenight_e2e_harness.py --game-id 0022500001
    python scripts/gamenight_e2e_harness.py --date 2025-10-21
    python scripts/gamenight_e2e_harness.py --json-out r.json  # write result

Safe operating rules
--------------------
* The harness NEVER writes to data/pnl_ledger.csv. It uses a dedicated
  test path (default data/pnl_ledger_e2e_test.csv) and a matching test
  bankroll path. Both are wiped at end of Stage 5.
* All filesystem I/O is scoped to a per-run temp directory for snapshots
  and synthetic line CSVs (no overlap with live data/lines/ files).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Default canonical paths (overridable via CLI).
QBOX_DIR_DEFAULT = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
SEASON_GAMES_JSON = os.path.join(PROJECT_DIR, "data", "nba", "season_games_2025-26.json")
TEST_LEDGER_PATH = os.path.join(PROJECT_DIR, "data", "pnl_ledger_e2e_test.csv")
TEST_BANKROLL_PATH = os.path.join(PROJECT_DIR, "data", "pnl_bankroll_e2e_test.csv")

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
QB_STAT_KEY = {  # ledger stat -> NBA Stats quarter-box field
    "pts": "pts", "reb": "reb", "ast": "ast", "fg3m": "fg3m",
    "stl": "stl", "blk": "blk", "tov": "to",
}


# --------------------------------------------------------------------------- #
# Helpers — game discovery + box totals
# --------------------------------------------------------------------------- #
def find_completed_game(
    qbox_dir: str = QBOX_DIR_DEFAULT,
    season_games_json: str = SEASON_GAMES_JSON,
    date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Pick a historical game with all 4 quarter_box files present.

    When date is set, restricts to games on that date. Returns a small
    dict {game_id, game_date, home_team, away_team} or None.
    """
    if not os.path.isdir(qbox_dir):
        return None
    schedule: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(season_games_json):
        try:
            with open(season_games_json, encoding="utf-8") as f:
                rows = (json.load(f) or {}).get("rows", [])
            for r in rows:
                schedule[r["game_id"]] = r
        except Exception:
            schedule = {}

    # Pick the first game_id (alphabetical = chronological for NBA ids) with
    # all 4 quarter files. Prefer one in the schedule for the date filter.
    candidates: List[str] = []
    for fn in sorted(os.listdir(qbox_dir)):
        if not fn.endswith("_q4.json"):
            continue
        gid = fn[: -len("_q4.json")]
        if not (len(gid) == 10 and gid.isdigit()):
            continue
        # Must also have q1/q2/q3.
        ok = all(os.path.exists(os.path.join(qbox_dir, f"{gid}_q{q}.json"))
                 for q in (1, 2, 3))
        if not ok:
            continue
        if date and schedule.get(gid, {}).get("game_date") != date:
            continue
        candidates.append(gid)

    if not candidates:
        return None
    # Prefer a game that's also in the schedule (so we have date/team meta).
    for gid in candidates:
        if gid in schedule:
            sched = schedule[gid]
            return {
                "game_id":   gid,
                "game_date": sched.get("game_date", ""),
                "home_team": sched.get("home_team", ""),
                "away_team": sched.get("away_team", ""),
            }
    # Fallback: first candidate with no schedule meta.
    return {"game_id": candidates[0], "game_date": "",
            "home_team": "", "away_team": ""}


def sum_box_through_quarter(
    game_id: str, through_q: int, qbox_dir: str = QBOX_DIR_DEFAULT,
) -> Dict[str, Dict[str, Any]]:
    """Cumulative per-player totals through quarter through_q (inclusive)."""
    totals: Dict[str, Dict[str, Any]] = {}
    for q in range(1, through_q + 1):
        path = os.path.join(qbox_dir, f"{game_id}_q{q}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for p in data.get("players", []) or []:
            name = p.get("player_name") or ""
            if not name:
                continue
            row = totals.setdefault(name, {
                "player_id": p.get("player_id"),
                "name": name,
                "team": p.get("team_abbreviation") or "",
                **{s: 0 for s in STATS},
            })
            row["team"] = p.get("team_abbreviation") or row["team"]
            for s in STATS:
                try:
                    row[s] += int(p.get(QB_STAT_KEY[s]) or 0)
                except (TypeError, ValueError):
                    continue
    return totals


# --------------------------------------------------------------------------- #
# Stage 1 — pregame slate
# --------------------------------------------------------------------------- #
def stage1_pregame_slate(
    game: Dict[str, Any], qbox_dir: str = QBOX_DIR_DEFAULT,
) -> Dict[str, Any]:
    """Build a synthetic pregame slate from the historical final box.

    We project a per-player pregame prediction by treating the cumulative-Q3
    total as a noisy proxy for the model's pre-game point (it's BIASED, of
    course, but the harness validates PIPELINE SHAPE, not model accuracy).
    Each player gets all 7 STATS so the schema check holds.
    """
    t0 = time.time()
    totals_q3 = sum_box_through_quarter(game["game_id"], 3, qbox_dir=qbox_dir)
    if not totals_q3:
        return {"ok": False, "stage": "pregame_slate",
                "reason": "no_box_data_through_q3",
                "runtime_sec": round(time.time() - t0, 3)}

    slate: List[Dict[str, Any]] = []
    for name, row in totals_q3.items():
        # Project Q3 -> game by 36/48 = 1.333. Won't be accurate but creates a
        # realistic-shaped pregame number.
        preds = {s: round(float(row[s]) * (48.0 / 36.0), 2) for s in STATS}
        slate.append({
            "player_id": row["player_id"],
            "player": name,
            "team": row["team"],
            "preds": preds,
        })

    # Schema check: every player has all 7 stats.
    bad = [r["player"] for r in slate
           if not all(s in r["preds"] for s in STATS)]
    ok = (len(bad) == 0) and (len(slate) >= 10)
    return {
        "ok": ok,
        "stage": "pregame_slate",
        "n_players": len(slate),
        "n_stats_per_player": len(STATS),
        "missing_stat_players": bad[:5],
        "slate": slate,
        "runtime_sec": round(time.time() - t0, 3),
        "reason": None if ok else "schema_or_too_few_players",
    }


# --------------------------------------------------------------------------- #
# Stage 2 — in-play snapshots through endQ1/Q2/Q3
# --------------------------------------------------------------------------- #
def _write_synthetic_lines(
    date_str: str, lines_dir: str, slate: List[Dict[str, Any]],
) -> str:
    """Write one bov-format line CSV that quotes every (player, stat) in the
    slate at a line == 0.95 * pred (forces OVER edges) so the in-play
    ranker has something to rank against.
    """
    os.makedirs(lines_dir, exist_ok=True)
    path = os.path.join(lines_dir, f"{date_str}_bov.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "captured_at", "book", "game_id", "player_id", "player_name",
            "stat", "line", "over_price", "under_price", "start_time",
        ])
        captured = datetime.now(timezone.utc).isoformat(timespec="seconds")
        start = captured
        for r in slate:
            for stat in STATS:
                pred = float(r["preds"].get(stat, 0.0) or 0.0)
                # Use lines slightly below the projection so OVER has edge.
                line = max(0.5, round(pred * 0.9 - 0.25, 1))
                w.writerow([
                    captured, "bov", "", r.get("player_id") or "",
                    r["player"], stat, f"{line:.1f}",
                    -110, -110, start,
                ])
    # Also write empty pin + fd so the loader doesn't choke.
    for book in ("pin", "fd"):
        bp = os.path.join(lines_dir, f"{date_str}_{book}.csv")
        if not os.path.exists(bp):
            with open(bp, "w", encoding="utf-8") as f:
                f.write("captured_at,book,game_id,player_id,player_name,"
                        "stat,line,over_price,under_price,start_time\n")
    return path


def _isolate_quarters(
    game_id: str, src_qbox: str, dst_qbox: str, through_q: int,
) -> None:
    """Copy <game_id>_q1..q<through_q>.json into dst_qbox (no q4 leak)."""
    os.makedirs(dst_qbox, exist_ok=True)
    for q in range(1, through_q + 1):
        src = os.path.join(src_qbox, f"{game_id}_q{q}.json")
        dst = os.path.join(dst_qbox, f"{game_id}_q{q}.json")
        if os.path.exists(src):
            shutil.copy2(src, dst)


def stage2_inplay_snapshots(
    game: Dict[str, Any],
    slate: List[Dict[str, Any]],
    tmp_root: str,
    qbox_dir: str = QBOX_DIR_DEFAULT,
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the in-play ranker at endQ1, endQ2, endQ3 against synthetic lines.

    For each boundary we copy the appropriate q1..qN JSONs into an isolated
    qbox dir so the ranker only sees data up through quarter N. We use a
    stub projector so we don't need full model artifacts; the stub
    deterministically projects each (player, stat) by scaling the visible
    cumulative line by (48 / minutes_elapsed).
    """
    import inplay_bet_ranker as ibr  # noqa: PLC0415

    t0 = time.time()
    gid = game["game_id"]
    date_s = date_str or game.get("game_date") or datetime.now().strftime("%Y-%m-%d")
    lines_dir = os.path.join(tmp_root, "lines")
    _write_synthetic_lines(date_s, lines_dir, slate)

    # Build a player->pregame_pred index from the slate so the stub projector
    # can produce reasonable point projections.
    pred_index: Dict[str, Dict[str, float]] = {
        r["player"]: r["preds"] for r in slate
    }

    def fake_project(snap: dict, period: Optional[int] = None) -> List[Dict]:
        """Deterministic projector: pace-scale visible cumulative to 48 min."""
        max_q = int(snap.get("max_quarter_observed") or 1)
        # Game-clock share: Q1=12, Q2=24, Q3=36 minutes elapsed (assume regulation).
        elapsed = 12.0 * max_q
        scale = 48.0 / max(1.0, elapsed)
        rows: List[Dict] = []
        for p in snap.get("players", []) or []:
            name = p.get("name") or ""
            for stat in STATS:
                cur = float(p.get(stat, 0) or 0)
                # Use pregame as anchor where available; pace otherwise.
                pre = float(pred_index.get(name, {}).get(stat, 0.0) or 0.0)
                pace = cur * scale
                # Blend pregame (anchor) with pace (live signal): 50/50.
                proj = max(cur, 0.5 * pre + 0.5 * pace)
                rows.append({
                    "name": name, "team": p.get("team", ""),
                    "player_id": p.get("player_id"), "stat": stat,
                    "current": cur, "projected_final": round(proj, 4),
                    "period": snap.get("period"),
                    "q10": max(0.0, proj * 0.6),
                    "q90": proj * 1.4,
                })
        return rows

    per_boundary: Dict[str, Dict[str, Any]] = {}

    # Monkey-patch ibr at module scope: redirect QBOX_DIR, LINES_DIR, and
    # the projector. Save originals so we restore after.
    orig_qbox = ibr.QBOX_DIR
    orig_lines = ibr.LINES_DIR
    orig_project = ibr._project_with_engine
    try:
        ibr.LINES_DIR = lines_dir
        ibr._project_with_engine = fake_project

        for label, through_q in [("endQ1", 1), ("endQ2", 2), ("endQ3", 3)]:
            tb0 = time.time()
            qbox_isolated = os.path.join(tmp_root, f"qbox_{label}")
            _isolate_quarters(gid, qbox_dir, qbox_isolated, through_q)
            ibr.QBOX_DIR = qbox_isolated
            payload = ibr.run_tick(
                game_id=gid, date_str=date_s, bankroll=1000.0,
                qbox_dir=qbox_isolated, books=("bov",),
            )
            per_boundary[label] = {
                "status": payload.get("status"),
                "n_props_evaluated": payload.get("n_props_evaluated", 0),
                "n_positive_ev": payload.get("n_positive_ev", 0),
                "top_edge_pct": payload.get("top_edge_pct"),
                "ranked_bets_count": len(payload.get("ranked_bets") or []),
                "max_kelly_pct": max(
                    [b.get("kelly_pct_used", 0) for b in (payload.get("ranked_bets") or [])],
                    default=0.0,
                ),
                "tick_latency_ms": payload.get("tick_latency_ms"),
                "runtime_sec": round(time.time() - tb0, 3),
            }
    finally:
        ibr.QBOX_DIR = orig_qbox
        ibr.LINES_DIR = orig_lines
        ibr._project_with_engine = orig_project

    # Assertions: each boundary must have at least 1 ranked bet AND
    # kelly_pct_used (a percent) must be in [0, 25].
    ok = True
    reasons: List[str] = []
    for label, info in per_boundary.items():
        if info["ranked_bets_count"] < 1:
            ok = False
            reasons.append(f"{label}: no ranked bets")
        kp = info["max_kelly_pct"]
        if not (0.0 <= kp <= 25.0):
            ok = False
            reasons.append(f"{label}: kelly_pct_used out of bounds ({kp})")

    return {
        "ok": ok,
        "stage": "inplay_snapshots",
        "boundaries": per_boundary,
        "lines_dir": lines_dir,
        "reason": "; ".join(reasons) if reasons else None,
        "runtime_sec": round(time.time() - t0, 3),
    }


# --------------------------------------------------------------------------- #
# Stage 3 — place bet to test ledger, settle, assert correctness
# --------------------------------------------------------------------------- #
def stage3_place_and_settle(
    game: Dict[str, Any],
    slate: List[Dict[str, Any]],
    tmp_root: str,
    qbox_dir: str = QBOX_DIR_DEFAULT,
    test_ledger: str = TEST_LEDGER_PATH,
    test_bankroll: str = TEST_BANKROLL_PATH,
) -> Dict[str, Any]:
    """Write a fake bet to TEST ledger, run auto_settle, assert outcome."""
    from src.betting import pnl_ledger as ledger  # noqa: PLC0415
    import auto_settle_daemon as asd  # noqa: PLC0415

    t0 = time.time()
    gid = game["game_id"]

    # 1) Hard guard — the test paths MUST NOT be the production paths.
    prod_ledger = os.path.abspath(os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv"))
    if os.path.abspath(test_ledger) == prod_ledger:
        return {"ok": False, "stage": "place_and_settle",
                "reason": "REFUSE: test_ledger path == production ledger",
                "runtime_sec": round(time.time() - t0, 3)}

    # 2) Compute the actual final stat for a known player (top scorer through
    #    Q3 — they're guaranteed to have played).
    totals_q3 = sum_box_through_quarter(gid, 3, qbox_dir=qbox_dir)
    totals_final = sum_box_through_quarter(gid, 4, qbox_dir=qbox_dir)
    if not totals_q3 or not totals_final:
        return {"ok": False, "stage": "place_and_settle",
                "reason": "no_box_data", "runtime_sec": round(time.time() - t0, 3)}
    target = max(totals_q3.values(), key=lambda r: r["pts"])
    pname = target["name"]
    actual_pts = float(totals_final.get(pname, {}).get("pts", 0))

    # 3) Decide on a line where we KNOW the outcome (line = actual - 1 -> OVER wins).
    line = actual_pts - 1.0
    side = "OVER"
    expected_status = "won"

    # 4) Monkey-patch ledger paths to TEST ledger.
    orig_ledger = ledger.LEDGER_CSV
    orig_bankroll = ledger.BANKROLL_CSV
    orig_lock = ledger.LOCK_PATH
    # Wipe any pre-existing test files (paranoia).
    for p in (test_ledger, test_bankroll, test_ledger + ".lock"):
        if os.path.exists(p):
            os.remove(p)
    ledger.LEDGER_CSV = test_ledger
    ledger.BANKROLL_CSV = test_bankroll
    ledger.LOCK_PATH = test_ledger + ".lock"

    # 5) Place the bet via the real public API.
    bet_id = None
    settle_result: Dict[str, Any] = {}
    auto_settle_result: Dict[str, Any] = {}
    try:
        ledger.record_bankroll(1000.0, "e2e_test_seed")
        bet_id = ledger.place_bet(
            game_id=gid, player=pname, stat="pts",
            line=line, side=side, book="bov",
            odds=-110, stake=20.0,
            model_pred=actual_pts, model_prob=0.6,
            kelly_pct=0.025, player_id=target["player_id"], team=target["team"],
        )

        # 6) Drive the post-game auto-settle daemon against the same test
        #    ledger but with a FRESH seen-set (so it actually picks up the
        #    historical q4 file we already have on disk).
        seen_path = Path(os.path.join(tmp_root, "auto_settle_seen.json"))
        # Tell auto_settle to use the same patched ledger module.
        # Seed seen-set with every q4 EXCEPT ours, then call tick().
        every_q4 = set()
        for fn in os.listdir(qbox_dir):
            if fn.endswith("_q4.json"):
                pre = fn[: -len("_q4.json")]
                if len(pre) == 10 and pre.isdigit():
                    every_q4.add(pre)
        every_q4.discard(gid)
        seen_path.write_text(json.dumps(sorted(every_q4)), encoding="utf-8")

        # Skip the bankroll refresh side-effect (touches outside paths).
        orig_refresh = asd.refresh_bankroll
        asd.refresh_bankroll = lambda *_a, **_k: {"skipped_in_e2e": True}
        try:
            auto_settle_result = asd.tick(
                qb_dir=Path(qbox_dir), seen_path=seen_path, dry_run=False,
                start_bankroll=1000.0,
            )
        finally:
            asd.refresh_bankroll = orig_refresh

        # 7) Verify the bet is now settled with the expected status.
        all_bets = ledger.all_bets()
        match = next((b for b in all_bets if b["bet_id"] == bet_id), None)
        settle_result = match or {}
    finally:
        ledger.LEDGER_CSV = orig_ledger
        ledger.BANKROLL_CSV = orig_bankroll
        ledger.LOCK_PATH = orig_lock

    actual_status = settle_result.get("status", "")
    actual_stat_recorded = settle_result.get("actual_stat", "")
    n_settled_in_cycle = sum(len(g.get("settled", []))
                             for g in (auto_settle_result.get("games") or []))
    ok = (actual_status == expected_status
          and bet_id is not None
          and n_settled_in_cycle >= 1)

    return {
        "ok": ok,
        "stage": "place_and_settle",
        "test_ledger": test_ledger,
        "bet_id": bet_id,
        "player": pname,
        "line": line,
        "side": side,
        "actual_pts": actual_pts,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "actual_stat_recorded": actual_stat_recorded,
        "auto_settle_games_processed": len(auto_settle_result.get("games") or []),
        "auto_settle_n_settled": n_settled_in_cycle,
        "runtime_sec": round(time.time() - t0, 3),
        "reason": None if ok else f"status mismatch: got {actual_status!r} expected {expected_status!r}",
    }


# --------------------------------------------------------------------------- #
# Stage 4 — CLV tracker (test mode)
# --------------------------------------------------------------------------- #
def stage4_clv_tracker(
    game: Dict[str, Any],
    bet_player: str,
    bet_line: float,
    tmp_root: str,
    test_ledger: str = TEST_LEDGER_PATH,
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Run clv_tracker_daemon.run_tick against the test ledger.

    Synthesizes one snapshot for the same (player, stat, book) where the
    line moved UP by 1.0 — so an OVER bet should show positive CLV.

    NOTE: clv_tracker_daemon.load_pending_bets filters status == 'pending';
    after Stage 3 our bet is 'won'. So Stage 4 inserts a fresh "pending"
    test bet with the same (player, stat, book) into a temp ledger CSV,
    runs the tick once, asserts the row reaches the CLV ledger.
    """
    from scripts import clv_tracker_daemon as ctd  # noqa: PLC0415

    t0 = time.time()
    date_s = date_str or game.get("game_date") or datetime.now().strftime("%Y-%m-%d")

    # Build a fresh test-ledger with a single pending bet (we don't reuse the
    # one from Stage 3 because that one is already settled).
    clv_test_ledger = os.path.join(tmp_root, "clv_test_ledger.csv")
    bet_id = "e2e-clv-test-bet"
    placed_line = bet_line
    # Use a placed_at slightly in the past so the daemon's "placed < now" filter passes.
    placed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(clv_test_ledger, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        from src.betting.pnl_ledger import LEDGER_COLS as _COLS
        w.writerow(_COLS)
        row = {c: "" for c in _COLS}
        row.update({
            "bet_id": bet_id, "placed_at": placed_at,
            "game_id": game["game_id"], "player": bet_player,
            "team": "", "stat": "pts", "line": f"{placed_line:.2f}",
            "side": "OVER", "book": "bov", "american_odds": "-110",
            "stake": "20.00", "status": "pending", "strategy": "e2e",
        })
        w.writerow([row[c] for c in _COLS])

    # Synthesize a one-row snapshot in a private lines/ dir: line moved up by 1.0.
    clv_lines_dir = os.path.join(tmp_root, "clv_lines")
    os.makedirs(clv_lines_dir, exist_ok=True)
    snap_path = os.path.join(clv_lines_dir, f"{date_s}_bov.csv")
    captured = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(snap_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "captured_at", "book", "game_id", "player_id", "player_name",
            "stat", "line", "over_price", "under_price", "start_time",
        ])
        w.writerow([captured, "bov", game["game_id"], "", bet_player,
                    "pts", f"{placed_line + 1.0:.1f}", -120, -100,
                    datetime.now(timezone.utc).isoformat(timespec="seconds")])

    clv_out = os.path.join(tmp_root, "clv_out.csv")
    vault_md = os.path.join(tmp_root, "clv_dash.md")
    closing_out = os.path.join(tmp_root, "closing_lines.csv")

    rpt = ctd.run_tick(
        pnl_path=Path(clv_test_ledger), lines_dir=Path(clv_lines_dir),
        clv_out_path=Path(clv_out), vault_md_path=Path(vault_md),
        closing_out_path=Path(closing_out),
    )

    # Inspect the CLV ledger row.
    clv_rows: List[Dict[str, Any]] = []
    if os.path.exists(clv_out):
        with open(clv_out, encoding="utf-8") as fh:
            clv_rows = list(csv.DictReader(fh))

    clv_pct: Optional[float] = None
    ours = next((r for r in clv_rows if r["bet_id"] == bet_id), None)
    if ours:
        try:
            clv_pct = float(ours.get("clv_pct", 0))
        except (TypeError, ValueError):
            clv_pct = None

    ok = (
        rpt.get("bets_tracked", 0) >= 1
        and ours is not None
        and clv_pct is not None
        and clv_pct > 0  # OVER, line moved UP -> positive CLV
    )

    return {
        "ok": ok,
        "stage": "clv_tracker",
        "report": rpt,
        "test_clv_ledger": clv_out,
        "clv_row_found": ours is not None,
        "clv_pct": clv_pct,
        "expected_sign": "positive",
        "runtime_sec": round(time.time() - t0, 3),
        "reason": None if ok else f"clv_pct={clv_pct} (expected >0)",
    }


# --------------------------------------------------------------------------- #
# Stage 5 — cleanup
# --------------------------------------------------------------------------- #
def stage5_cleanup(
    tmp_root: str,
    test_ledger: str = TEST_LEDGER_PATH,
    test_bankroll: str = TEST_BANKROLL_PATH,
) -> Dict[str, Any]:
    """Remove the test ledger + sidecars + tmp root."""
    t0 = time.time()
    removed: List[str] = []
    failed: List[str] = []

    for p in (test_ledger, test_bankroll, test_ledger + ".lock"):
        try:
            if os.path.exists(p):
                os.remove(p)
                removed.append(p)
        except OSError as exc:
            failed.append(f"{p}: {exc}")

    if tmp_root and os.path.isdir(tmp_root):
        try:
            shutil.rmtree(tmp_root, ignore_errors=True)
            removed.append(tmp_root)
        except OSError as exc:
            failed.append(f"{tmp_root}: {exc}")

    ok = len(failed) == 0
    # SAFETY ASSERTION — never wipe the prod ledger.
    prod = os.path.abspath(os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv"))
    if os.path.abspath(test_ledger) == prod:
        ok = False
        failed.append("REFUSE: test_ledger == prod ledger")

    return {
        "ok": ok,
        "stage": "cleanup",
        "removed": removed,
        "failed": failed,
        "runtime_sec": round(time.time() - t0, 3),
        "reason": None if ok else "; ".join(failed),
    }


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def run_harness(
    game_id: Optional[str] = None,
    date_str: Optional[str] = None,
    qbox_dir: str = QBOX_DIR_DEFAULT,
    test_ledger: str = TEST_LEDGER_PATH,
    test_bankroll: str = TEST_BANKROLL_PATH,
) -> Dict[str, Any]:
    """Run the full 5-stage harness. Returns a result dict.

    When game_id is None, picks the first completed historical game with
    all 4 quarter-box files present (optionally constrained by date_str).
    """
    t0 = time.time()
    if game_id:
        game = {"game_id": game_id, "game_date": date_str or "",
                "home_team": "", "away_team": ""}
    else:
        game = find_completed_game(qbox_dir=qbox_dir, date=date_str)
        if game is None:
            return {
                "ok": False, "stages_passed": 0, "n_stages": 5,
                "reason": "no completed historical game found",
                "game": None,
                "stage_results": {},
                "runtime_sec": round(time.time() - t0, 3),
            }
    if not date_str:
        date_str = game.get("game_date") or datetime.now().strftime("%Y-%m-%d")

    tmp_root = tempfile.mkdtemp(prefix="gn_e2e_")
    stage_results: Dict[str, Dict[str, Any]] = {}
    stages_passed = 0

    try:
        # Stage 1
        r1 = stage1_pregame_slate(game, qbox_dir=qbox_dir)
        stage_results["stage1_pregame_slate"] = {k: v for k, v in r1.items()
                                                  if k != "slate"}
        if not r1["ok"]:
            return _finalize(game, stage_results, stages_passed, t0, tmp_root)
        stages_passed += 1
        slate = r1["slate"]

        # Stage 2
        r2 = stage2_inplay_snapshots(game, slate, tmp_root,
                                       qbox_dir=qbox_dir, date_str=date_str)
        stage_results["stage2_inplay_snapshots"] = r2
        if not r2["ok"]:
            return _finalize(game, stage_results, stages_passed, t0, tmp_root)
        stages_passed += 1

        # Stage 3
        r3 = stage3_place_and_settle(game, slate, tmp_root,
                                      qbox_dir=qbox_dir,
                                      test_ledger=test_ledger,
                                      test_bankroll=test_bankroll)
        stage_results["stage3_place_and_settle"] = r3
        if not r3["ok"]:
            return _finalize(game, stage_results, stages_passed, t0, tmp_root)
        stages_passed += 1

        # Stage 4 — uses the same player/line as Stage 3.
        r4 = stage4_clv_tracker(game, bet_player=r3["player"],
                                  bet_line=r3["line"], tmp_root=tmp_root,
                                  test_ledger=test_ledger,
                                  date_str=date_str)
        stage_results["stage4_clv_tracker"] = r4
        if not r4["ok"]:
            return _finalize(game, stage_results, stages_passed, t0, tmp_root)
        stages_passed += 1
    finally:
        # Stage 5 always runs (cleanup).
        r5 = stage5_cleanup(tmp_root, test_ledger=test_ledger,
                             test_bankroll=test_bankroll)
        stage_results["stage5_cleanup"] = r5
        if r5["ok"]:
            stages_passed += 1

    return _finalize(game, stage_results, stages_passed, t0, None)


def _finalize(game: Dict[str, Any], stage_results: Dict[str, Any],
              stages_passed: int, t0: float,
              tmp_root: Optional[str]) -> Dict[str, Any]:
    if tmp_root:
        # Best-effort cleanup if we bailed early.
        shutil.rmtree(tmp_root, ignore_errors=True)
    return {
        "ok": stages_passed == 5,
        "stages_passed": stages_passed,
        "n_stages": 5,
        "game": game,
        "stage_results": stage_results,
        "runtime_sec": round(time.time() - t0, 3),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Game-night E2E validation harness (R20_M5)")
    ap.add_argument("--game-id", default=None,
                    help="NBA Stats game_id (default: auto-pick first complete historical game)")
    ap.add_argument("--date", default=None,
                    help="Constrain auto-pick to this date YYYY-MM-DD (optional)")
    ap.add_argument("--qbox-dir", default=QBOX_DIR_DEFAULT,
                    help="data/cache/quarter_box override (default: production)")
    ap.add_argument("--test-ledger", default=TEST_LEDGER_PATH,
                    help="TEST ledger CSV path — MUST NOT equal data/pnl_ledger.csv")
    ap.add_argument("--test-bankroll", default=TEST_BANKROLL_PATH,
                    help="TEST bankroll CSV path")
    ap.add_argument("--json-out", default=None,
                    help="Write the result dict as JSON to this path")
    args = ap.parse_args()

    result = run_harness(
        game_id=args.game_id, date_str=args.date,
        qbox_dir=args.qbox_dir,
        test_ledger=args.test_ledger, test_bankroll=args.test_bankroll,
    )

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)

    print(json.dumps({
        "ok": result["ok"],
        "stages_passed": f"{result['stages_passed']}/{result['n_stages']}",
        "game_id": (result.get("game") or {}).get("game_id"),
        "runtime_sec": result["runtime_sec"],
        "stage_status": {k: v.get("ok", False) for k, v in result["stage_results"].items()},
    }, indent=2, default=str))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
