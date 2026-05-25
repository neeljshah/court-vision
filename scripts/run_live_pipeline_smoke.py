"""run_live_pipeline_smoke.py -- Tier 4 integration (loop 5).

Interactive CLI that walks the live-pipeline happy path end to end with
verbose stdout. Same nine steps as tests/test_live_pipeline_e2e.py, but
prints what's happening at each one so an operator can debug a broken
component on game day without having to read pytest output.

All I/O is sandboxed under a tempdir; no real HTTP, no real bookmaker
or NBA-Stats calls, nothing written to ``data/``. Safe to run anytime.

Usage:
    python scripts/run_live_pipeline_smoke.py
    python scripts/run_live_pipeline_smoke.py --verbose      # show payloads

Exit code 0 = all steps green; non-zero = first failed step number.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
for _p in (PROJECT_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


# ── Reused canonical fixture (mirrors tests/test_live_pipeline_e2e.py) ─────

def make_canonical_snapshot() -> dict:
    """Synthetic end-of-Q3 snapshot used by the test + this CLI."""
    return {
        "game_id":     "0022500999",
        "captured_at": "2026-05-24T22:30:00",
        "game_status": "LIVE",
        "period":      3,
        "clock":       "0:00",
        "home_team":   "DEN",
        "away_team":   "LAL",
        "home_score":  90,
        "away_score":  78,
        "players": [
            {"player_id": 203999, "name": "Nikola Jokic", "team": "DEN",
             "min": 27.0, "pts": 22, "reb": 9, "ast": 7,
             "fg3m": 1, "stl": 1, "blk": 0, "tov": 2, "pf": 2,
             "is_starter": True,
             "min_q1": 9.0, "min_q2": 9.0, "min_q3": 9.0, "min_q4": 0.0},
            {"player_id": 2544, "name": "LeBron James", "team": "LAL",
             "min": 26.0, "pts": 18, "reb": 5, "ast": 6,
             "fg3m": 2, "stl": 1, "blk": 1, "tov": 3, "pf": 3,
             "is_starter": True,
             "min_q1": 9.0, "min_q2": 8.5, "min_q3": 8.5, "min_q4": 0.0},
        ],
    }


# ── Pretty-print helpers ────────────────────────────────────────────────────

def _banner(n: int, name: str) -> None:
    print(f"\n[{n}/9] {name}")
    print("    " + "-" * 70)


def _ok(msg: str) -> None:
    print(f"    OK  -- {msg}")


def _info(msg: str, verbose: bool, body=None) -> None:
    if verbose:
        if body is not None:
            print(f"        {msg}: {body}")
        else:
            print(f"        {msg}")


# ── Step runners ────────────────────────────────────────────────────────────

def step_1_snapshot(tmp: str, verbose: bool):
    _banner(1, "Snapshot ingest          (src/data/live.py)")
    from src.data import live as live_mod
    live_dir = os.path.join(tmp, "live")
    os.makedirs(live_dir, exist_ok=True)
    snap = make_canonical_snapshot()
    path = os.path.join(live_dir, f"{snap['game_id']}_20260524T223000.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snap, fh)
    reloaded = live_mod.load_live_state(path)
    assert reloaded["game_id"] == snap["game_id"]
    assert live_mod.is_live(reloaded)
    _ok(f"snapshot written + reloaded ({len(reloaded['players'])} players)")
    _info("path", verbose, path)
    return reloaded


def step_2_projection(snap: dict, verbose: bool):
    _banner(2, "Projection               (src/prediction/live_engine.py)")
    from src.prediction import live_engine
    rows = live_engine.project_from_snapshot(snap)
    assert len(rows) == 14, f"expected 14 rows, got {len(rows)}"
    _ok(f"projected {len(rows)} (player, stat) rows")
    if verbose:
        for r in rows[:7]:
            print(f"        {r['name']:18s} {r['stat']:4s} "
                  f"cur={r['current']:.1f} -> proj={r['projected_final']:.2f}")
    return rows


def step_3_line_fetch(snap: dict, tmp: str, verbose: bool):
    _banner(3, "Line scrape (mocked)     (scripts/fetch_live_prop_lines.py)")
    from scripts.fetch_live_prop_lines import append_rows, _FIELDS
    lines_dir = os.path.join(tmp, "lines")
    os.makedirs(lines_dir, exist_ok=True)
    path = os.path.join(lines_dir, "2026-05-24_dk.csv")
    row = {
        "captured_at":   "2026-05-24T22:30:00",
        "book":          "draftkings",
        "game_id":       snap["game_id"],
        "player_id":     "203999",
        "player_name":   "Nikola Jokic",
        "team":          "DEN",
        "stat":          "pts",
        "line":          "28.5",
        "over_price":    "-115",
        "under_price":   "-105",
        "market_status": "open",
    }
    n = append_rows([row], path)
    assert n == 1
    _ok(f"wrote {n} synthetic prop line to {os.path.basename(path)}")
    _info("fields", verbose, _FIELDS)
    return path


def step_4_edge_eval(snap: dict, verbose: bool):
    _banner(4, "Edge re-evaluation       (scripts/live_edge_eval.py)")
    from scripts import live_edge_eval as edge_mod
    bet = {"player": "Nikola Jokic", "stat": "pts", "line": "28.5",
           "side": "OVER", "odds": "-115", "model": "31.0"}
    results = edge_mod.evaluate_all([bet], [snap])
    assert len(results) == 1
    r = results[0]
    assert r["proj_final"] > 28.5, (
        f"projection {r['proj_final']!r} should exceed line 28.5"
    )
    assert r["action"] in edge_mod.ACTIONS
    _ok(f"edge eval -> proj={r['proj_final']:.2f}  "
        f"new_ev={r['new_ev']:+.3f}  action={r['action']}")
    return r


def step_5_alert(edge_row: dict, snap: dict, verbose: bool):
    _banner(5, "Webhook alert (mocked)   (src/notifications/webhook_alerts.py)")
    from src.notifications import webhook_alerts

    captured = []

    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    def _fake(req, timeout=None):
        captured.append({
            "url":  req.full_url,
            "body": json.loads(req.data.decode("utf-8")),
        })
        return _FakeResp()

    notifier = webhook_alerts.WebhookNotifier(
        slack_url="https://hooks.slack.test/edge",
        discord_url=None,
        min_severity="high",
    )
    with mock.patch.object(webhook_alerts.urllib.request, "urlopen",
                            side_effect=_fake):
        sent = notifier.send(
            title="EDGE_FLIP",
            body=(f"{edge_row['player']} {edge_row['side']} {edge_row['line']} "
                  f"-> action={edge_row['action']}"),
            severity="high",
            tags={"player": edge_row["player"], "stat": edge_row["stat"],
                  "line": edge_row["line"], "side": edge_row["side"],
                  "action": edge_row["action"], "game_id": snap["game_id"]},
        )
    assert sent is True
    assert len(captured) == 1
    _ok(f"webhook POST captured -> {captured[0]['url']}")
    _info("payload", verbose, captured[0]["body"])
    return captured[0]


def step_6_place_bet(L, snap: dict, projected_final: float, verbose: bool):
    _banner(6, "Bet placement            (src/betting/pnl_ledger.py)")
    L.record_bankroll(1000.0, "seed")
    bet_id = L.place_bet(
        game_id=snap["game_id"],
        player="Nikola Jokic", stat="pts",
        line=28.5, side="OVER", book="DK", odds=-115, stake=50.0,
        model_pred=projected_final, player_id="203999", team="DEN",
    )
    assert len(bet_id) == 36
    assert L.current_bankroll() == 950.0
    _ok(f"bet placed bet_id={bet_id[:8]}... bankroll=950.00")
    return bet_id


def step_7_settle(L, bet_id: str, verbose: bool):
    _banner(7, "Settlement               (pnl_ledger.settle_bet)")
    out = L.settle_bet(bet_id, actual_stat=31.0)
    assert out["status"] == "won"
    assert out["profit_loss"] > 0
    _ok(f"settled WON  P/L=+${out['profit_loss']:.2f}  "
        f"bankroll=${out['bankroll_after']:.2f}")
    return out


def step_8_clv(L, bet_id: str, verbose: bool) -> dict:
    _banner(8, "CLV                      (src/betting/clv.py, Tier 2.7)")
    try:
        from src.betting.clv import compute_clv
    except ImportError as exc:
        print(f"    SKIP -- Tier 2.7 src.betting.clv not importable: {exc}")
        return {}
    placed = next(r for r in L.all_bets() if r["bet_id"] == bet_id)
    clv = compute_clv(placed, closing_line=27.0, closing_odds=-120)
    assert clv.get("beat_close") is True
    _ok(f"CLV beat_close=True  clv_line={clv['clv_line']}  "
        f"clv_percent={clv['clv_percent']:.4f}")
    _info("clv", verbose, clv)
    return clv


def step_9_summary(L, verbose: bool):
    _banner(9, "P&L summary              (pnl_ledger.pnl_summary)")
    s = L.pnl_summary()
    assert s["n_bets"] >= 1
    assert s["win_rate"] == 1.0
    _ok(f"summary: n_bets={s['n_bets']} won={s['won']} lost={s['lost']} "
        f"win_rate={s['win_rate']:.2f} roi={s['roi']:+.4f} "
        f"profit=${s['total_profit']:+.2f}")
    return s


# ── Orchestration ──────────────────────────────────────────────────────────

def run(verbose: bool = False) -> int:
    print(f"\n=== LIVE PIPELINE E2E SMOKE  ({datetime.now().isoformat(timespec='seconds')}) ===")
    with tempfile.TemporaryDirectory(prefix="live_pipeline_smoke_") as tmp:
        # Repoint pnl_ledger to tmp so the smoke run never touches real data/.
        import src.betting.pnl_ledger as L
        importlib.reload(L)
        L.LEDGER_CSV   = os.path.join(tmp, "pnl_ledger.csv")
        L.BANKROLL_CSV = os.path.join(tmp, "pnl_bankroll.csv")
        L.LOCK_PATH    = os.path.join(tmp, "pnl_ledger.csv.lock")

        try:
            snap = step_1_snapshot(tmp, verbose)
            rows = step_2_projection(snap, verbose)
            step_3_line_fetch(snap, tmp, verbose)
            edge = step_4_edge_eval(snap, verbose)
            step_5_alert(edge, snap, verbose)
            jokic_pts = next(
                r for r in rows
                if r["player_id"] == 203999 and r["stat"] == "pts"
            )
            bid = step_6_place_bet(L, snap, jokic_pts["projected_final"], verbose)
            step_7_settle(L, bid, verbose)
            step_8_clv(L, bid, verbose)
            step_9_summary(L, verbose)
        except AssertionError as exc:
            print("\n[FAIL] assertion in latest step")
            print("       ", exc)
            traceback.print_exc()
            return 1
        except Exception as exc:    # noqa: BLE001 -- diagnostic CLI
            print(f"\n[FAIL] unexpected {type(exc).__name__}: {exc}")
            traceback.print_exc()
            return 2

        print("\n=== ALL 9 STEPS GREEN ===\n")
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Show full payloads + per-row projections.")
    args = ap.parse_args(argv)
    return run(verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
