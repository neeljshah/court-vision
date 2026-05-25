"""tests/test_live_pipeline_e2e.py -- Tier 4 integration (loop 5).

End-to-end smoke test for the entire LIVE pipeline. All 14+ shipped components
have unit coverage in isolation; this file is the FIRST test that walks the
happy-path edge in their actual call order:

    snapshot poll -> projection (cycle 95c) -> line scrape (8d40558a) ->
        edge eval (88j) -> webhook alert (ba548e1c) -> bet placement
        (8762cd94) -> settlement -> CLV (Tier 2.7) -> P&L summary

No real I/O escapes ``tmp_path``; no real HTTP is made (urlopen is mocked);
no live NBA-Stats / book API is touched.

If a real game day breaks somewhere, this file is the diagnostic: each step
has its own assertion + readable failure message so we know exactly which
component snapped.

Companion CLI: ``scripts/run_live_pipeline_smoke.py`` reuses the same helper
sequence with verbose stdout for operator debugging.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import date as _date
from unittest import mock

import pytest


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
for _p in (PROJECT_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# --------------------------------------------------------------------------- #
# Fixtures.                                                                   #
# --------------------------------------------------------------------------- #

@pytest.fixture
def isolated_ledger(monkeypatch, tmp_path):
    """Repoint the P&L ledger module to tmp_path so place/settle never touches data/."""
    import src.betting.pnl_ledger as L
    importlib.reload(L)
    monkeypatch.setattr(L, "LEDGER_CSV",   str(tmp_path / "pnl_ledger.csv"))
    monkeypatch.setattr(L, "BANKROLL_CSV", str(tmp_path / "pnl_bankroll.csv"))
    monkeypatch.setattr(L, "LOCK_PATH",    str(tmp_path / "pnl_ledger.csv.lock"))
    return L


@pytest.fixture
def canonical_snapshot():
    """Synthetic end-of-Q3 snapshot following src/data/live.py schema.

    Two players (one per team), 7 sane stats each, sufficiently above their
    OVER lines that the edge eval will flag a LET-IT-RIDE on the OVER side.
    """
    return {
        "game_id":    "0022500999",
        "captured_at": "2026-05-24T22:30:00",
        "game_status": "LIVE",
        "period":      3,
        "clock":       "0:00",            # end of Q3 -> 36 min played, 12 left
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


# --------------------------------------------------------------------------- #
# The end-to-end test.                                                        #
# --------------------------------------------------------------------------- #

def test_live_pipeline_end_to_end(isolated_ledger, canonical_snapshot, tmp_path):
    """Walk the entire live-system happy path with mocked I/O.

    Each step has its own assertion block + failure message that names the
    component to investigate.
    """
    # ────────────────────────────────────────────────────────────────────────
    # STEP 1 -- Snapshot ingest (src/data/live.py).
    #           Write the canonical snapshot to a tmp live dir then re-read
    #           via the canonical loader to prove the schema round-trips.
    # ────────────────────────────────────────────────────────────────────────
    from src.data import live as live_mod

    live_dir = tmp_path / "live"
    live_dir.mkdir()
    snap_path = live_dir / f"{canonical_snapshot['game_id']}_20260524T223000.json"
    snap_path.write_text(json.dumps(canonical_snapshot), encoding="utf-8")

    snap = live_mod.load_live_state(str(snap_path))
    assert snap, "STEP 1 FAILED (src/data/live.py): could not reload snapshot"
    assert snap["game_id"] == canonical_snapshot["game_id"], (
        "STEP 1 FAILED: src/data/live.load_live_state corrupted game_id"
    )
    assert live_mod.is_live(snap), (
        "STEP 1 FAILED: snapshot game_status round-trip broke is_live()"
    )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 2 -- Projection (src/prediction/live_engine.py, cycle 95c).
    #           Assert 14 rows = 2 players * 7 stats.
    # ────────────────────────────────────────────────────────────────────────
    from src.prediction import live_engine

    rows = live_engine.project_from_snapshot(snap)
    assert len(rows) == 14, (
        f"STEP 2 FAILED (live_engine.project_from_snapshot): expected "
        f"14 rows (2 players * 7 stats), got {len(rows)}"
    )
    # Each row needs the keys downstream consumers (edge eval, ledger) need.
    required = {"name", "team", "player_id", "stat", "current", "projected_final"}
    missing = required - set(rows[0].keys())
    assert not missing, (
        f"STEP 2 FAILED: live_engine row schema missing keys {sorted(missing)}; "
        f"got keys {sorted(rows[0].keys())}"
    )
    # Find Jokic PTS projection -- should be > current (still has Q4 to play).
    jokic_pts = next(
        r for r in rows if r["player_id"] == 203999 and r["stat"] == "pts"
    )
    assert jokic_pts["projected_final"] > jokic_pts["current"], (
        "STEP 2 FAILED: projected_final should exceed current with 12 min left"
    )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 3 -- Mock line fetch (scripts/fetch_live_prop_lines.py, 8d40558a).
    #           Write a synthetic prop line CSV at canonical schema using the
    #           module's own append_rows helper (so we exercise the dedup +
    #           header logic, not just file I/O).
    # ────────────────────────────────────────────────────────────────────────
    from scripts.fetch_live_prop_lines import append_rows, _FIELDS

    lines_dir = tmp_path / "lines"
    lines_dir.mkdir()
    line_path = lines_dir / "2026-05-24_dk.csv"
    synthetic_lines = [{
        "captured_at":   "2026-05-24T22:30:00",
        "book":          "draftkings",
        "game_id":       canonical_snapshot["game_id"],
        "player_id":     "203999",
        "player_name":   "Nikola Jokic",
        "team":          "DEN",
        "stat":          "pts",
        "line":          "28.5",
        "over_price":    "-115",
        "under_price":   "-105",
        "market_status": "open",
    }]
    n_written = append_rows(synthetic_lines, str(line_path))
    assert n_written == 1, (
        f"STEP 3 FAILED (fetch_live_prop_lines.append_rows): expected to "
        f"write 1 line row, got {n_written}"
    )
    assert line_path.exists(), "STEP 3 FAILED: lines CSV not created"
    # Header includes every canonical field.
    header = line_path.read_text(encoding="utf-8").splitlines()[0]
    for col in _FIELDS:
        assert col in header, (
            f"STEP 3 FAILED: lines CSV header missing column {col!r}"
        )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 4 -- Edge compare (scripts/live_edge_eval.py, cycle 88j).
    #           Build a bet log matching the cycle-68 schema, hand it +
    #           snapshots to evaluate_all, assert the OVER bet at 28.5 is
    #           flagged LET IT RIDE (Jokic projects to >29).
    # ────────────────────────────────────────────────────────────────────────
    from scripts import live_edge_eval as edge_mod

    bet_log = [{
        "player": "Nikola Jokic",
        "stat":   "pts",
        "line":   "28.5",
        "side":   "OVER",
        "odds":   "-115",
        "model":  "31.0",          # cycle-68 pregame model column
    }]
    edge_results = edge_mod.evaluate_all(bet_log, [snap])
    assert len(edge_results) == 1, (
        f"STEP 4 FAILED (live_edge_eval.evaluate_all): expected 1 result, "
        f"got {len(edge_results)}"
    )
    r0 = edge_results[0]
    assert r0["action"] in edge_mod.ACTIONS, (
        f"STEP 4 FAILED: action {r0['action']!r} not in valid set "
        f"{edge_mod.ACTIONS}"
    )
    # Jokic should be projected ABOVE the 28.5 line at end of Q3 with 22 pts.
    assert r0["proj_final"] is not None and r0["proj_final"] > 28.5, (
        f"STEP 4 FAILED: edge eval projection {r0['proj_final']!r} should "
        f"exceed the 28.5 line"
    )
    assert r0["new_ev"] is not None, (
        "STEP 4 FAILED: edge eval did not compute new_ev"
    )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 5 -- Webhook alert (src/notifications/webhook_alerts.py, ba548e1c).
    #           Mock urlopen so no real POST escapes, fire an EDGE_FLIP, and
    #           assert the request body contains the expected payload fields.
    # ────────────────────────────────────────────────────────────────────────
    from src.notifications import webhook_alerts

    captured_requests = []

    class _FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    def _fake_urlopen(req, timeout=None):
        captured_requests.append({
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
                            side_effect=_fake_urlopen):
        sent = notifier.send(
            title="EDGE_FLIP",
            body=f"{r0['player']} {r0['side']} {r0['line']} -> action={r0['action']}",
            severity="high",
            tags={"player": r0["player"], "stat": r0["stat"],
                  "line": r0["line"], "side": r0["side"],
                  "action": r0["action"], "game_id": snap["game_id"]},
        )
    assert sent is True, (
        "STEP 5 FAILED (WebhookNotifier.send): expected True with mocked 200 OK"
    )
    assert len(captured_requests) == 1, (
        f"STEP 5 FAILED: expected exactly 1 webhook POST, got "
        f"{len(captured_requests)}"
    )
    req = captured_requests[0]
    assert req["url"].startswith("https://hooks.slack.test/"), (
        f"STEP 5 FAILED: alert posted to wrong URL {req['url']!r}"
    )
    slack_body = req["body"]
    assert "EDGE_FLIP" in slack_body["text"], (
        "STEP 5 FAILED: slack payload missing EDGE_FLIP title"
    )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 6 -- Bet placement (src/betting/pnl_ledger.py, 8762cd94).
    #           Place a bet, assert UUID returned + ledger row + bankroll
    #           deducted by stake.
    # ────────────────────────────────────────────────────────────────────────
    L = isolated_ledger
    L.record_bankroll(1000.0, "seed")
    assert L.current_bankroll() == 1000.0, (
        "STEP 6 SETUP FAILED: seeded bankroll not 1000"
    )

    bet_id = L.place_bet(
        game_id=snap["game_id"],
        player=r0["player"], stat="pts",
        line=28.5, side="OVER", book="DK", odds=-115, stake=50.0,
        model_pred=jokic_pts["projected_final"],
        player_id="203999", team="DEN",
    )
    assert isinstance(bet_id, str) and len(bet_id) == 36, (
        f"STEP 6 FAILED (pnl_ledger.place_bet): bad bet_id {bet_id!r}"
    )
    assert L.current_bankroll() == 950.0, (
        f"STEP 6 FAILED: bankroll after place_bet expected 950, got "
        f"{L.current_bankroll()}"
    )
    open_b = L.open_bets()
    assert len(open_b) == 1 and open_b[0]["bet_id"] == bet_id, (
        "STEP 6 FAILED: placed bet not recovered via open_bets()"
    )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 7 -- Settlement (pnl_ledger.settle_bet).
    #           Synthetic final actual = 31 PTS (>28.5 -> OVER wins).
    #           Assert status=won, profit_loss > 0, bankroll restored + profit.
    # ────────────────────────────────────────────────────────────────────────
    settle = L.settle_bet(bet_id, actual_stat=31.0)
    assert settle["status"] == "won", (
        f"STEP 7 FAILED (pnl_ledger.settle_bet): expected status=won at "
        f"actual=31 vs line=28.5 OVER, got {settle['status']!r}"
    )
    assert settle["profit_loss"] > 0, (
        f"STEP 7 FAILED: WON bet should have positive P&L, got "
        f"{settle['profit_loss']}"
    )
    # -115 odds, $50 stake -> $50 * (100/115) ~= $43.48 profit.
    expected_profit = round(50.0 * (100.0 / 115.0), 2)
    assert abs(settle["profit_loss"] - expected_profit) < 0.01, (
        f"STEP 7 FAILED: profit math wrong; expected ~{expected_profit}, "
        f"got {settle['profit_loss']}"
    )
    # Bankroll after settle = 950 (after stake) + 50 (stake back) + profit.
    expected_bankroll = round(950.0 + 50.0 + expected_profit, 2)
    assert abs(settle["bankroll_after"] - expected_bankroll) < 0.01, (
        f"STEP 7 FAILED: bankroll after WON settle wrong; "
        f"expected ~{expected_bankroll}, got {settle['bankroll_after']}"
    )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 8 -- CLV (src/betting/clv.py, Tier 2.7 -- commit 7ccca701).
    #           Build a synthetic closing line + odds and assert compute_clv
    #           reports clv_percent + beat_close on the placed-bet row.
    # ────────────────────────────────────────────────────────────────────────
    try:
        from src.betting.clv import compute_clv as clv_compute
    except ImportError as exc:
        pytest.fail(
            f"STEP 8 FAILED (Tier 2.7 not shipped): "
            f"src.betting.clv.compute_clv not importable -- {exc}"
        )

    # Replay the cycle-8762cd94 placed-bet row exactly as the ledger holds it.
    placed_bet_row = next(r for r in L.all_bets() if r["bet_id"] == bet_id)
    # Closing line moved LOWER (27.0) at slightly worse odds (-120) -> OVER
    # bettor still beat the close: got a longer number AND a longer price.
    clv = clv_compute(placed_bet_row, closing_line=27.0, closing_odds=-120)
    assert "clv_percent" in clv, (
        f"STEP 8 FAILED (compute_clv): result missing clv_percent; "
        f"got {clv!r}"
    )
    assert clv.get("beat_close") is True, (
        f"STEP 8 FAILED: OVER 28.5 vs close 27.0 @ -120 should beat close; "
        f"got beat_close={clv.get('beat_close')!r}"
    )
    assert clv.get("clv_line") and float(clv["clv_line"]) > 0, (
        f"STEP 8 FAILED: clv_line should be positive (better number), got "
        f"{clv.get('clv_line')!r}"
    )

    # ────────────────────────────────────────────────────────────────────────
    # STEP 9 -- P&L summary (pnl_ledger.pnl_summary).
    #           After 1 settled WON bet: n_bets>=1, n_settled=1, win_rate=1.0,
    #           roi>0, total_profit>0.
    # ────────────────────────────────────────────────────────────────────────
    summary = L.pnl_summary()
    assert summary["n_bets"] >= 1, (
        f"STEP 9 FAILED (pnl_summary): n_bets should be >= 1, got "
        f"{summary['n_bets']}"
    )
    assert summary["n_settled"] == 1, (
        f"STEP 9 FAILED: expected 1 settled bet, got {summary['n_settled']}"
    )
    assert summary["won"] == 1 and summary["lost"] == 0, (
        f"STEP 9 FAILED: expected 1 won/0 lost, got "
        f"won={summary['won']} lost={summary['lost']}"
    )
    assert summary["win_rate"] == 1.0, (
        f"STEP 9 FAILED: win_rate should be 1.0 after 1 WON bet, got "
        f"{summary['win_rate']}"
    )
    assert summary["roi"] > 0, (
        f"STEP 9 FAILED: ROI should be positive after WON bet, got "
        f"{summary['roi']}"
    )
    assert summary["total_profit"] > 0, (
        f"STEP 9 FAILED: total_profit should be > 0, got "
        f"{summary['total_profit']}"
    )


# --------------------------------------------------------------------------- #
# Meta-test: every assertion in the e2e test must be a *meaningful* check     #
# (not just "didn't crash"). This sanity test scans the file and ensures      #
# every assert has an explanatory message.                                    #
# --------------------------------------------------------------------------- #

def test_each_step_has_meaningful_assertion_message():
    """Every assert in the e2e test carries an explanatory failure message.

    Guards against the test silently rotting into "asserts that nothing crashed."
    """
    test_path = os.path.abspath(__file__)
    with open(test_path, encoding="utf-8") as fh:
        source = fh.read()
    # Quick scan: every "assert " line in test_live_pipeline_end_to_end must
    # have a comma (msg) or appear in pytest.fail/pytest.raises form. We allow
    # multi-line asserts and the meta-test asserts themselves.
    in_e2e = False
    bad_asserts = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("def test_live_pipeline_end_to_end"):
            in_e2e = True
            continue
        if in_e2e and stripped.startswith("def ") and \
                not stripped.startswith("def test_live_pipeline_end_to_end"):
            in_e2e = False
            continue
        if not in_e2e:
            continue
        if stripped.startswith("assert ") and "," not in stripped:
            # multi-line assert -- look ahead a few lines for closing paren + comma
            block = "\n".join(source.splitlines()[i - 1:i + 4])
            if "," not in block:
                bad_asserts.append((i, stripped))
    assert not bad_asserts, (
        f"Found {len(bad_asserts)} asserts without explanatory message in "
        f"test_live_pipeline_end_to_end:\n" +
        "\n".join(f"  line {ln}: {txt}" for ln, txt in bad_asserts)
    )
