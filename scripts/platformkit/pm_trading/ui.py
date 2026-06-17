"""ui.py -- a self-contained betting DASHBOARD (static HTML, no server needed).

Renders, from REAL data only:
  - LIVE NOW: games in progress (keyless live scores) with the model's last
    logged in-game win probability,
  - TODAY: the pregame slate with model probabilities (settled ones marked),
  - TRACK RECORD: predictions logged / settled / accuracy / Brier (reuses
    status.py), and the paper P&L,
  - an honest banner: PAPER, no real money, no edge claimed.

Open the generated file in any browser. No frameworks, no keys, read-only.
Run: python -m scripts.platformkit.pm_trading.ui  (writes + prints the path)
"""
from __future__ import annotations

import datetime as _dt
import html
import pathlib
import sys
from typing import Optional

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import status as _status  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_OUT = _ROOT / "data" / "pm_trading" / "ui" / "dashboard.html"

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0c0f14;color:#e6edf3;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:24px}
h1{font-size:22px;letter-spacing:.3px}h2{font-size:14px;text-transform:uppercase;letter-spacing:2px;color:#7d8da5;margin:26px 0 12px}
.banner{background:#1b2230;border:1px solid #2b3a52;border-radius:10px;padding:10px 14px;color:#9fb3d1;font-size:13px;margin:10px 0 4px}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.stat{background:#141a24;border:1px solid #232c3a;border-radius:12px;padding:14px 18px;min-width:130px}
.stat .k{color:#7d8da5;font-size:11px;text-transform:uppercase;letter-spacing:1px}
.stat .v{font-size:24px;font-weight:600;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:#141a24;border:1px solid #232c3a;border-radius:14px;padding:16px}
.row{display:flex;justify-content:space-between;align-items:center}
.team{font-weight:600;font-size:17px}.muted{color:#7d8da5;font-size:12px}
.pill{font-size:10px;font-weight:700;letter-spacing:1px;padding:3px 8px;border-radius:999px}
.live{background:#3b1d1d;color:#ff6b6b}.final{background:#1d2b1d;color:#6bd47f}.sched{background:#1d2533;color:#7d8da5}
.bar{height:10px;border-radius:6px;background:#2a3446;margin:12px 0 6px;overflow:hidden}
.fill{height:100%;background:linear-gradient(90deg,#3b82f6,#22d3ee)}
.pct{display:flex;justify-content:space-between;font-size:12px;color:#9fb3d1}
.ok{color:#6bd47f}.no{color:#ff6b6b}
footer{margin-top:28px;color:#62708a;font-size:12px;border-top:1px solid #1c2531;padding-top:14px}
"""


def _bar(p_home: float, home: str, away: str) -> str:
    pct = max(0, min(100, round(p_home * 100)))
    return ("<div class='bar'><div class='fill' style='width:%d%%'></div></div>"
            "<div class='pct'><span>%s %d%%</span><span>%s %d%%</span></div>"
            % (pct, html.escape(home), pct, html.escape(away), 100 - pct))


def _esc(x) -> str:
    return html.escape(str(x))


def _latest_prob_by_game(df, layer):
    """Map game_id -> calibrated_prob of the latest row for that layer."""
    if df is None or len(df) == 0:
        return {}
    sub = df[df["layer"] == layer].sort_values("pred_ts")
    out = {}
    for _, r in sub.iterrows():
        out[str(r.get("game_id", ""))] = (float(r["calibrated_prob"]),
                                          r.get("outcome"))
    return out


def build_dashboard(ledger_dir: Optional[str] = None, include_live: bool = True,
                    now_iso: str = "") -> str:
    rep = _status.status_report(ledger_dir=ledger_dir)
    try:
        from scripts.platformkit.ledger.ledger import read_ledger
        df = read_ledger(base_dir=ledger_dir)
    except Exception:
        df = None

    live_cards = ""
    if include_live:
        try:
            from live_ingame import MLBLiveStateSource
            games = MLBLiveStateSource().fetch()
        except Exception:
            games = []
        ig = _latest_prob_by_game(df, "ingame")
        for g in games:
            prob = ig.get(str(g.game_id), (None, None))[0]
            bar = _bar(prob, g.home, g.away) if prob is not None else \
                "<div class='muted'>model prob pending next in-game tick</div>"
            live_cards += (
                "<div class='card'><div class='row'><span class='team'>%s @ %s</span>"
                "<span class='pill live'>LIVE</span></div>"
                "<div class='muted'>inning %s %s &middot; %s %s - %s %s</div>%s</div>"
                % (_esc(g.away), _esc(g.home), _esc(g.inning), _esc(g.half),
                   _esc(g.away), _esc(g.away_runs), _esc(g.home), _esc(g.home_runs),
                   bar))
    if not live_cards:
        live_cards = "<div class='muted'>No games live right now.</div>"

    today = (now_iso or _dt.datetime.now().isoformat())[:10]
    pg_cards = ""
    pg = _latest_prob_by_game(df, "pregame")
    if df is not None and len(df):
        seen = set()
        sub = df[(df["layer"] == "pregame")].sort_values("pred_ts")
        for _, r in sub.iterrows():
            gid = str(r.get("game_id", ""))
            if gid in seen or str(r.get("game_date", "")) != today:
                continue
            seen.add(gid)
            prob, outcome = pg.get(gid, (float(r["calibrated_prob"]), None))
            status_pill = "final" if outcome == outcome and outcome is not None \
                else "sched"
            label = ("WON" if (outcome == 1 and prob >= .5) or (outcome == 0 and prob < .5)
                     else "LOST") if (outcome is not None and outcome == outcome) else "scheduled"
            cls = "ok" if label == "WON" else ("no" if label == "LOST" else "muted")
            pg_cards += (
                "<div class='card'><div class='row'><span class='team'>%s @ %s</span>"
                "<span class='pill %s'>%s</span></div>%s"
                "<div class='muted %s'>%s</div></div>"
                % (_esc(r["away"]), _esc(r["home"]), status_pill,
                   ("FINAL" if status_pill == "final" else "PREGAME"),
                   _bar(float(prob), str(r["home"]), str(r["away"])), cls, label))
    if not pg_cards:
        pg_cards = "<div class='muted'>No pregame predictions logged for today yet.</div>"

    paper = rep.get("paper") or {}
    stats = [
        ("Predictions", rep.get("n_predictions", 0)),
        ("Settled", rep.get("n_graded", 0)),
        ("Accuracy", rep.get("accuracy", "--")),
        ("Brier", rep.get("brier", "--")),
        ("Paper P&L", "$%s" % paper.get("net_paper_pnl", 0)),
    ]
    stat_html = "".join("<div class='stat'><div class='k'>%s</div>"
                        "<div class='v'>%s</div></div>" % (k, _esc(v))
                        for k, v in stats)

    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='refresh' content='30'>"
            "<title>PM-Trading Dashboard</title><style>%s</style></head><body>"
            "<h1>PM-Trading Dashboard</h1>"
            "<div class='banner'>PAPER MODE &middot; no real money, no real orders &middot; "
            "model is calibrated, NO betting edge is claimed &middot; go-live is HUMAN-CONFIRM</div>"
            "<div class='stats'>%s</div>"
            "<h2>Live now</h2><div class='grid'>%s</div>"
            "<h2>Today's slate</h2><div class='grid'>%s</div>"
            "<footer>standing: %s<br>%s</footer></body></html>"
            % (_CSS, stat_html, live_cards, pg_cards,
               _esc(rep.get("standing", "")), _esc(rep.get("note", ""))))


def write_dashboard(path: Optional[str] = None, ledger_dir: Optional[str] = None,
                    include_live: bool = True) -> str:
    out = pathlib.Path(path) if path else _OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_dashboard(ledger_dir=ledger_dir, include_live=include_live),
                   encoding="utf-8")
    return str(out)


def serve(port: int = 8787, ledger_dir: Optional[str] = None,
          include_live: bool = True) -> None:
    """Live-updating server: regenerates fresh data on every request. The page
    auto-refreshes every 30s. PAPER/read-only; bound to localhost."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = build_dashboard(ledger_dir=ledger_dir,
                                   include_live=include_live).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence
            return

    srv = HTTPServer(("127.0.0.1", port), _H)
    print("serving PAPER dashboard at http://127.0.0.1:%d (Ctrl-C to stop)" % port)
    srv.serve_forever()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Generate the paper betting dashboard")
    ap.add_argument("--out", default="", help="output html path")
    ap.add_argument("--no-live", action="store_true", help="skip live fetch")
    ap.add_argument("--serve", type=int, nargs="?", const=8787, default=0,
                    help="serve live-updating UI on PORT (default 8787)")
    a = ap.parse_args(argv)
    if a.serve:
        serve(port=a.serve, include_live=not a.no_live)
        return 0
    p = write_dashboard(path=a.out or None, include_live=not a.no_live)
    print("dashboard written: %s" % p)
    print("open it in a browser (file://%s)" % p.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
