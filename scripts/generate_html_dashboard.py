"""generate_html_dashboard.py -- tier4-13 (loop 5). Mobile-friendly HTML view.

Self-contained HTML dashboard for game-night operators away from the laptop.
Output is one HTML file with INLINE CSS, NO external <link>/<script>/font
URLs, so the operator can scp to phone or open from a LAN HTTP server.

Sections rendered:
    1. Header: timestamp + bankroll + open bet count + today's P&L
    2. Active games (1 row per game; top-3 players' current/projection)
    3. Open bets (player/stat/line/side/current/projection/live edge/status)
    4. Today's top-10 edge recommendations (endQ2 if halftime, else compare_to_lines pregame)
    5. A/B strategy P&L summary (last 7 days)

Vanilla HTML + inline CSS only. No JS framework. No external fetches at
render time. ``<meta http-equiv="refresh">`` lets the phone auto-refresh
when --refresh-sec is non-zero.

CLI:
    python scripts/generate_html_dashboard.py --date 2026-05-24 --output dash.html
    python scripts/generate_html_dashboard.py --refresh-sec 60
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import date as _date, datetime
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


# ── data loaders (each best-effort; any failure -> empty section) ────────────

def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def load_active_games(date_iso: str) -> List[Dict]:
    """Return [{game_id, header, players: [{name, team, pts_now, pts_proj, ...}]}].

    Pulls latest snapshot per game from data/live/ and runs
    live_engine.project_from_snapshot. Returns top-3 players per game
    (by current PTS).
    """
    try:
        from src.data.live import list_today_snapshots, load_live_state
        from src.prediction import live_engine
    except Exception:
        return []

    paths = _safe(list_today_snapshots, date_iso) or []
    out = []
    for path in paths:
        snap = _safe(load_live_state, path)
        if not snap:
            continue
        try:
            rows = live_engine.project_from_snapshot(snap)
        except Exception:
            rows = []

        # Group rows -> per-player aggregate (one PTS row per player)
        by_pid: Dict = {}
        for r in rows:
            pid = r.get("player_id")
            if pid is None:
                continue
            d = by_pid.setdefault(pid, {
                "name": r.get("name", "?"),
                "team": r.get("team", ""),
                "stats": {},
            })
            stat = (r.get("stat") or "").lower()
            d["stats"][stat] = {
                "current": float(r.get("current", 0) or 0),
                "projected": float(r.get("projected_final", 0) or 0),
            }

        players = sorted(
            by_pid.values(),
            key=lambda p: -(p["stats"].get("pts", {}).get("current", 0)),
        )[:3]

        out.append({
            "game_id": snap.get("game_id", ""),
            "home_team": snap.get("home_team", "HOME"),
            "away_team": snap.get("away_team", "AWAY"),
            "home_score": snap.get("home_score", 0),
            "away_score": snap.get("away_score", 0),
            "period": snap.get("period", "?"),
            "clock": snap.get("clock", "?"),
            "status": snap.get("game_status", "?"),
            "players": players,
        })
    return out


def load_open_bets_with_live_edge(active_games: List[Dict]) -> List[Dict]:
    """Open bets joined against live projections for edge column."""
    try:
        from src.betting.pnl_ledger import open_bets
    except Exception:
        return []

    bets = _safe(open_bets) or []

    # Build lookup: (player_lower, stat) -> projection
    proj_lookup: Dict = {}
    for g in active_games:
        for p in g["players"]:
            for stat, v in p["stats"].items():
                proj_lookup[(p["name"].lower(), stat)] = v["projected"]
                proj_lookup[(p["name"].lower(), stat, "current")] = v["current"]

    out = []
    for b in bets:
        player = b.get("player", "")
        stat = (b.get("stat") or "").lower()
        try:
            line = float(b.get("line", 0) or 0)
        except (TypeError, ValueError):
            line = 0.0
        proj = proj_lookup.get((player.lower(), stat))
        cur = proj_lookup.get((player.lower(), stat, "current"))
        edge = (proj - line) if proj is not None else None
        out.append({
            "player": player,
            "team": b.get("team", ""),
            "stat": stat,
            "line": line,
            "side": b.get("side", ""),
            "book": b.get("book", ""),
            "stake": b.get("stake", ""),
            "current": cur,
            "projection": proj,
            "live_edge": edge,
            "status": b.get("status", "open"),
        })
    return out


def load_pnl_summary() -> Dict:
    try:
        from src.betting.pnl_ledger import (
            pnl_summary, current_bankroll, open_bets,
        )
    except Exception:
        return {"current_bankroll": 0.0, "n_open": 0, "today_profit": 0.0}

    sm = _safe(pnl_summary, "1d") or {}
    return {
        "current_bankroll": _safe(current_bankroll) or 0.0,
        "n_open": len(_safe(open_bets) or []),
        "today_profit": sm.get("total_profit", 0.0),
        "today_settled": sm.get("n_settled", 0),
    }


def load_recommendations(date_iso: str, active_games: List[Dict]) -> List[Dict]:
    """Top-10 edges. Halftime -> recommend_endQ2_bets; else empty list (operator
    runs compare_to_lines manually with their own CSV).
    """
    # Detect halftime in any active game
    halftime = any(
        (str(g.get("period")) in ("2", "3") and
         str(g.get("clock", "")).strip() in ("0:00", "00:00", "12:00", "12:0"))
        for g in active_games
    )
    if not halftime:
        return []
    try:
        sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
        import recommend_endQ2_bets as rec
        from src.data.live import list_today_snapshots, load_live_state
        paths = list_today_snapshots(date_iso) or []
        snaps = []
        for p in paths:
            s = load_live_state(p)
            if s and rec.is_halftime_snapshot(s):
                snaps.append((p, s))
        out = rec.build_recommendations(snaps, threshold=1.0,
                                         include_pts_tov=False,
                                         date_iso=date_iso)
        return out[:10]
    except Exception:
        return []


def load_ab_summary() -> List[Dict]:
    """Per-strategy 7-day P&L summary."""
    try:
        from src.betting.ab_strategy import list_strategies, strategy_summary
    except Exception:
        return []
    strats = _safe(list_strategies) or []
    out = []
    for s in strats:
        name = s.get("strategy", "")
        if not name:
            continue
        sm = _safe(strategy_summary, name, "7d") or {}
        out.append({
            "strategy": name,
            "n_bets": sm.get("n_bets", 0),
            "n_settled": sm.get("n_settled", 0),
            "won": sm.get("won", 0),
            "lost": sm.get("lost", 0),
            "roi": sm.get("roi", 0.0),
            "total_profit": sm.get("total_profit", 0.0),
            "bankroll_cap": sm.get("bankroll_cap", 0.0),
        })
    return out


# ── HTML rendering ────────────────────────────────────────────────────────────

_CSS = """
  * { box-sizing: border-box; }
  body { background:#0e1116; color:#d8dee9; font-family:-apple-system,
         BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; font-size:14px;
         margin:0; padding:8px; }
  h1 { font-size:18px; margin:6px 0; color:#88c0d0; }
  h2 { font-size:16px; margin:14px 0 6px; color:#a3be8c;
       border-bottom:1px solid #2e3440; padding-bottom:3px; }
  .stat-bar { background:#1c2128; padding:10px; border-radius:6px;
              margin-bottom:10px; }
  .stat-bar span { display:inline-block; margin-right:14px; }
  .stat-bar b { color:#ebcb8b; }
  table { width:100%; border-collapse:collapse; margin-bottom:12px;
          font-size:13px; }
  th,td { padding:5px 6px; text-align:left;
          border-bottom:1px solid #2e3440; }
  th { background:#1c2128; color:#88c0d0; font-weight:600; }
  .num { font-family:'SF Mono','Consolas',monospace; text-align:right; }
  .pos { color:#a3be8c; }
  .neg { color:#bf616a; }
  .muted { color:#616e88; font-style:italic; padding:8px; }
  .game-head { background:#1c2128; padding:6px 10px; margin-top:8px;
               border-radius:4px; }
  .game-head .vs { font-weight:600; color:#88c0d0; }
  .game-head .clock { color:#ebcb8b; margin-left:8px; }
  @media (max-width:600px) {
    body { padding:4px; font-size:13px; }
    table { font-size:12px; }
    th,td { padding:3px 4px; }
  }
"""


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _num(x, fmt: str = "{:.2f}") -> str:
    if x is None or x == "":
        return "-"
    try:
        return fmt.format(float(x))
    except (TypeError, ValueError):
        return _esc(x)


def _signed_cell(x, fmt: str = "{:+.2f}") -> str:
    if x is None or x == "":
        return "<td class='num'>-</td>"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return f"<td class='num'>{_esc(x)}</td>"
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    return f"<td class='num {cls}'>{fmt.format(v)}</td>"


def _section_header(pnl: Dict, ts: str) -> str:
    return (
        f"<div class='stat-bar'>"
        f"<span>Updated <b>{_esc(ts)}</b></span>"
        f"<span>Bankroll <b>${_num(pnl.get('current_bankroll'))}</b></span>"
        f"<span>Open bets <b>{_esc(pnl.get('n_open', 0))}</b></span>"
        f"<span>Today P&amp;L <b>${_num(pnl.get('today_profit'))}</b> "
        f"({_esc(pnl.get('today_settled', 0))} settled)</span>"
        f"</div>"
    )


def _section_games(games: List[Dict]) -> str:
    parts = ["<h2>Active games</h2>"]
    if not games:
        parts.append("<div class='muted'>(no active games)</div>")
        return "".join(parts)
    for g in games:
        parts.append(
            f"<div class='game-head'><span class='vs'>"
            f"{_esc(g['away_team'])} {_esc(g['away_score'])} @ "
            f"{_esc(g['home_team'])} {_esc(g['home_score'])}</span>"
            f"<span class='clock'>Q{_esc(g['period'])} {_esc(g['clock'])} "
            f"[{_esc(g['status'])}]</span></div>"
        )
        parts.append(
            "<table><thead><tr><th>Player</th><th>Team</th>"
            "<th class='num'>PTS</th><th class='num'>PTS proj</th>"
            "<th class='num'>REB</th><th class='num'>REB proj</th>"
            "<th class='num'>AST</th><th class='num'>AST proj</th>"
            "</tr></thead><tbody>"
        )
        for p in g["players"]:
            s = p["stats"]
            row = "<tr>"
            row += f"<td>{_esc(p['name'])}</td><td>{_esc(p['team'])}</td>"
            for k in ("pts", "reb", "ast"):
                v = s.get(k, {})
                row += f"<td class='num'>{_num(v.get('current'), '{:.0f}')}</td>"
                row += f"<td class='num'>{_num(v.get('projected'), '{:.1f}')}</td>"
            row += "</tr>"
            parts.append(row)
        parts.append("</tbody></table>")
    return "".join(parts)


def _section_bets(bets: List[Dict]) -> str:
    parts = ["<h2>Open bets</h2>"]
    if not bets:
        parts.append("<div class='muted'>(no open bets)</div>")
        return "".join(parts)
    parts.append(
        "<table><thead><tr><th>Player</th><th>Stat</th>"
        "<th class='num'>Line</th><th>Side</th>"
        "<th class='num'>Cur</th><th class='num'>Proj</th>"
        "<th class='num'>Live edge</th><th>Status</th>"
        "</tr></thead><tbody>"
    )
    for b in bets:
        signed_edge = b.get("live_edge")
        if signed_edge is not None and b.get("side") == "UNDER":
            signed_edge = -signed_edge
        parts.append("<tr>")
        parts.append(f"<td>{_esc(b['player'])}</td>")
        parts.append(f"<td>{_esc(b['stat'].upper())}</td>")
        parts.append(f"<td class='num'>{_num(b['line'])}</td>")
        parts.append(f"<td>{_esc(b['side'])}</td>")
        parts.append(f"<td class='num'>{_num(b.get('current'), '{:.0f}')}</td>")
        parts.append(f"<td class='num'>{_num(b.get('projection'), '{:.1f}')}</td>")
        parts.append(_signed_cell(signed_edge))
        parts.append(f"<td>{_esc(b['status'])}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _section_recs(recs: List[Dict]) -> str:
    parts = ["<h2>Top recommendations (halftime endQ2)</h2>"]
    if not recs:
        parts.append("<div class='muted'>(no halftime recommendations right now)</div>")
        return "".join(parts)
    parts.append(
        "<table><thead><tr><th>Player</th><th>Stat</th>"
        "<th class='num'>Line</th><th class='num'>Proj</th>"
        "<th class='num'>Edge</th><th>Side</th>"
        "<th class='num'>EV/$</th><th class='num'>Kelly%</th>"
        "</tr></thead><tbody>"
    )
    for r in recs:
        parts.append("<tr>")
        parts.append(f"<td>{_esc(r.get('player'))}</td>")
        parts.append(f"<td>{_esc(str(r.get('stat','')).upper())}</td>")
        parts.append(f"<td class='num'>{_num(r.get('line'))}</td>")
        parts.append(f"<td class='num'>{_num(r.get('projection'))}</td>")
        parts.append(_signed_cell(r.get('edge')))
        parts.append(f"<td>{_esc(r.get('side'))}</td>")
        parts.append(_signed_cell(r.get('ev_per_dollar'), "{:+.4f}"))
        parts.append(f"<td class='num'>{_num(r.get('kelly_pct'))}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _section_ab(ab: List[Dict]) -> str:
    parts = ["<h2>A/B strategies (last 7d)</h2>"]
    if not ab:
        parts.append("<div class='muted'>(no strategies registered)</div>")
        return "".join(parts)
    parts.append(
        "<table><thead><tr><th>Strategy</th>"
        "<th class='num'>Bankroll</th><th class='num'>N</th>"
        "<th class='num'>W-L</th><th class='num'>ROI</th>"
        "<th class='num'>Profit</th></tr></thead><tbody>"
    )
    for s in ab:
        parts.append("<tr>")
        parts.append(f"<td>{_esc(s['strategy'])}</td>")
        parts.append(f"<td class='num'>${_num(s['bankroll_cap'])}</td>")
        parts.append(f"<td class='num'>{_esc(s['n_bets'])}</td>")
        parts.append(f"<td class='num'>{_esc(s['won'])}-{_esc(s['lost'])}</td>")
        parts.append(_signed_cell(s['roi'], "{:+.4f}"))
        parts.append(_signed_cell(s['total_profit'], "${:+.2f}"))
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def render_dashboard(date_iso: str, refresh_sec: int = 0) -> str:
    """Build the full HTML document. Pure function -- no file IO."""
    games = load_active_games(date_iso) or []
    bets = load_open_bets_with_live_edge(games)
    pnl = load_pnl_summary()
    recs = load_recommendations(date_iso, games)
    ab = load_ab_summary()
    ts = datetime.now().isoformat(timespec="seconds")

    meta_refresh = (
        f'<meta http-equiv="refresh" content="{int(refresh_sec)}">'
        if refresh_sec and refresh_sec > 0 else ""
    )
    doc = (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"{meta_refresh}"
        f"<title>NBA Live Dashboard {_esc(date_iso)}</title>"
        f"<style>{_CSS}</style></head><body>"
        f"<h1>NBA Live Dashboard &mdash; {_esc(date_iso)}</h1>"
        f"{_section_header(pnl, ts)}"
        f"{_section_games(games)}"
        f"{_section_bets(bets)}"
        f"{_section_recs(recs)}"
        f"{_section_ab(ab)}"
        "</body></html>"
    )
    return doc


def write_dashboard(path: str, date_iso: str, refresh_sec: int = 0) -> int:
    """Render + atomically write. Returns bytes written."""
    doc = render_dashboard(date_iso, refresh_sec=refresh_sec)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(doc)
    os.replace(tmp, path)
    return len(doc.encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="Date YYYY-MM-DD (default: today)")
    ap.add_argument("--output", default=os.path.join(
        PROJECT_DIR, "data", "dashboard.html"),
                    help="Output HTML path")
    ap.add_argument("--refresh-sec", type=int, default=0,
                    help="Auto-refresh interval (0=off)")
    args = ap.parse_args()

    date_iso = args.date or _date.today().isoformat()
    nbytes = write_dashboard(args.output, date_iso,
                              refresh_sec=args.refresh_sec)
    print(f"[ok] wrote {args.output} ({nbytes} bytes) for {date_iso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
