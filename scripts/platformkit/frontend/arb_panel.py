"""scripts.platformkit.frontend.arb_panel — honest money panel: arb/line-shop/CLV.

HONEST (binding): markets are efficient — NO model edge is claimed. Value =
line-shopping / devig / CLV ONLY (>=2 books).  edge_claimed is ALWAYS False.
Activates /api/arb + /api/clv on the :8099 board app (replaces dormant routes).

Public API: SPORTS, to_platform_id, build_arb_panel, build_all_arb,
            build_clv_panel, build_all_clv, render_arb_html, attach_money_routes.
"""
from __future__ import annotations

import argparse, html, json, logging, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.frontend import feed_multi, snapshot_scheduler
from scripts.platformkit.frontend.feed import OddsFeed
from scripts.platformkit.frontend.feed_multi import distinct_books

logger = logging.getLogger(__name__)

SPORTS: Tuple[str, ...] = ("basketball_nba", "mlb_sbro", "soccer_fd", "tennis_atp")

_PLATFORM_ID: Dict[str, str] = {
    "nba": "basketball_nba", "mlb": "mlb_sbro",
    "soccer": "soccer_fd", "tennis": "tennis_atp",
}

_HONEST_BANNER = (
    "HONEST MONEY PANEL: Markets are efficient — NO model edge claimed. "
    "Value = line-shopping / devig / CLV ONLY (cross-book, NOT model alpha). "
    "Arb + CLV activate only when >=2 distinct books price the same outcome."
)

_CSS = ("*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,"
        "BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;"
        "padding:24px 16px}.banner{background:#1e293b;border:1px solid #334155;"
        "border-left:4px solid #10b981;border-radius:6px;padding:14px 18px;"
        "margin-bottom:24px;font-size:.85rem;color:#94a3b8;line-height:1.5}"
        ".banner strong{color:#34d399}h1{font-size:1.4rem;font-weight:700;"
        "color:#f1f5f9;margin-bottom:6px}h2{font-size:1.05rem;font-weight:600;"
        "color:#cbd5e1;border-bottom:1px solid #1e293b;padding-bottom:4px;"
        "margin:18px 0 10px}.status{font-size:.8rem;margin-bottom:14px;"
        "padding:6px 10px;border-radius:4px;display:inline-block}"
        ".active{background:#0f2d1a;color:#86efac}.dormant{background:#1e293b;"
        "color:#64748b}.row{font-size:.85rem;padding:8px 10px;"
        "border-left:2px solid #10b981;margin-bottom:5px;background:#111827;"
        "border-radius:0 4px 4px 0}.empty{font-size:.85rem;color:#475569;"
        "font-style:italic;padding:6px 0}")


def to_platform_id(sport: str) -> str:
    """Accept friendly ('nba') OR platform id ('basketball_nba') -> platform id."""
    if sport in SPORTS:
        return sport
    return _PLATFORM_ID.get(sport.lower().strip(), sport)


def build_arb_panel(sport: str, feed: OddsFeed, *,
                    devig_method: str = "multiplicative",
                    min_middle_width: float = 0.5) -> Dict[str, Any]:
    """Build the arb/line-shop panel dict for one sport."""
    pid = to_platform_id(sport)
    try:
        games = feed.fetch(pid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_arb_panel: feed.fetch(%s) raised: %s", pid, exc)
        games = []
    scan = feed_multi.scan_games(games, devig_method=devig_method,
                                 min_middle_width=min_middle_width)
    max_books = max((distinct_books(g) for g in games), default=0)
    return {
        "sport": pid, "banner": _HONEST_BANNER, "n_games": len(games),
        "max_books": max_books,
        "status": "active" if scan["n_multibook_games"] >= 1 else "dormant",
        "arbitrage": scan["arbitrage"], "middles": scan["middles"],
        "devig": scan["devig"], "n_multibook_games": scan["n_multibook_games"],
        "note": scan["note"], "edge_claimed": False,
    }


def build_all_arb(feed: OddsFeed, sports: Tuple[str, ...] = SPORTS,
                  **kw: Any) -> Dict[str, Any]:
    """Build arb panels for all sports; flatten arb rows across sports."""
    per_sport = {pid: build_arb_panel(pid, feed, **kw) for pid in sports}
    rows = [dict(arb, sport=pid) for pid, p in per_sport.items()
            for arb in p.get("arbitrage", [])]
    status = "active" if any(p["status"] == "active" for p in per_sport.values()) else "dormant"
    n_multi = sum(p["n_multibook_games"] for p in per_sport.values())
    note = ("Cross-book line-shop / arb scan across all sports (NOT model alpha)."
            if status == "active"
            else "No multi-book games found — arb/CLV dormant until >=2 books.")
    return {"banner": _HONEST_BANNER, "status": status, "rows": rows,
            "per_sport": per_sport, "n_multibook_games": n_multi,
            "edge_claimed": False, "note": note}


def build_clv_panel(sport: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """Build the forward-CLV candidates panel for one sport."""
    pid = to_platform_id(sport)
    c = snapshot_scheduler.forward_clv_candidates(pid, root=root)
    return {
        "sport": pid, "banner": _HONEST_BANNER,
        "status": "active" if c["n_candidates"] > 0 else "dormant",
        "n_candidates": c["n_candidates"], "candidates": c["candidates"],
        "edge_claimed": False, "note": c["honest_note"],
    }


def build_all_clv(sports: Tuple[str, ...] = SPORTS,
                  root: Optional[Path] = None) -> Dict[str, Any]:
    """Build CLV panels for all sports; flatten candidates across sports."""
    per_sport = {pid: build_clv_panel(pid, root=root) for pid in sports}
    rows = [dict(cand, sport=pid) for pid, p in per_sport.items()
            for cand in p.get("candidates", [])]
    status = "active" if any(p["status"] == "active" for p in per_sport.values()) else "dormant"
    note = ("Forward CLV candidates across sports — opener->closer pairs for grading."
            if status == "active"
            else "No CLV candidates yet — need >=2 snapshots per (game,book,market,side).")
    return {"banner": _HONEST_BANNER, "status": status, "rows": rows,
            "per_sport": per_sport, "edge_claimed": False, "note": note}


def render_arb_html(panel: Dict[str, Any]) -> str:
    """Self-contained HTML; escapes everything; honest NO model edge banner."""
    sp = html.escape(str(panel.get("sport", "unknown")).upper())
    bn = html.escape(str(panel.get("banner", _HONEST_BANNER)))
    status = str(panel.get("status", "dormant"))
    arb_rows = panel.get("arbitrage") or []
    mid_rows = panel.get("middles") or []
    note = html.escape(str(panel.get("note", "")))

    def _arb_li(a: Dict[str, Any]) -> str:
        ev = html.escape(str(a.get("event_id", "?")))
        mkt = html.escape(str(a.get("market", "?")))
        ret = a.get("return_pct")
        ret_s = f"{ret:.2f}%" if isinstance(ret, (int, float)) else "?"
        legs_s = " | ".join(
            f"{html.escape(str(lg.get('side','?')))}@{html.escape(str(lg.get('book','?')))}"
            f"({html.escape(str(lg.get('decimal_odds','?')))})"
            for lg in (a.get("legs") or []))
        return f'<div class="row">{ev} [{mkt}] return={ret_s} — {legs_s}</div>'

    def _mid_li(m: Dict[str, Any]) -> str:
        w = m.get("width")
        return (f'<div class="row">'
                f'{html.escape(str(m.get("event_id","?")))} '
                f'[{html.escape(str(m.get("market","?")))}] '
                f'width={f"{w:.1f}" if isinstance(w,(int,float)) else "?"}</div>')

    arb_html = ("\n".join(_arb_li(a) for a in arb_rows)
                if arb_rows else '<div class="empty">No cross-book arbitrage found.</div>')
    mid_html = ("\n".join(_mid_li(m) for m in mid_rows)
                if mid_rows else '<div class="empty">No middles found.</div>')
    n_games = panel.get("n_games", 0)
    n_multi = panel.get("n_multibook_games", 0)
    return (
        f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8">'
        f'<title>Money Panel &mdash; {sp}</title>'
        f'<style>{_CSS}</style></head><body>\n'
        f'<div class="banner"><strong>NO model edge</strong> &mdash; {bn}</div>\n'
        f'<h1>Money Panel &mdash; {sp}</h1>\n'
        f'<div class="status {html.escape(status)}">{html.escape(status.upper())}</div>\n'
        f'<p style="font-size:.8rem;color:#64748b;margin-bottom:16px">'
        f'Games: {n_games} | Multi-book: {n_multi}</p>\n'
        f'<h2>Arbitrage Opportunities</h2>\n{arb_html}\n'
        f'<h2>Middles</h2>\n{mid_html}\n'
        f'<p style="font-size:.75rem;color:#475569;margin-top:20px">{note}</p>\n'
        '</body></html>')


def attach_money_routes(app: Any, feed: OddsFeed,
                        root: Optional[Path] = None) -> None:
    """Register 5 routes; lazy-import HTMLResponse so module is safe without fastapi."""
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    @app.get("/api/arb")
    def api_arb_all() -> Dict[str, Any]:
        return build_all_arb(feed)

    @app.get("/api/arb/{sport}")
    def api_arb_sport(sport: str) -> Dict[str, Any]:
        return build_arb_panel(sport, feed)

    @app.get("/arb/{sport}.html", response_class=HTMLResponse)
    def arb_sport_html(sport: str) -> str:
        return render_arb_html(build_arb_panel(sport, feed))

    @app.get("/api/clv")
    def api_clv_all() -> Dict[str, Any]:
        return build_all_clv(root=root)

    @app.get("/api/clv/{sport}")
    def api_clv_sport(sport: str) -> Dict[str, Any]:
        return build_clv_panel(sport, root=root)


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="arb_panel: honest money panel (NO model edge).")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--clv", action="store_true")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--html", action="store_true", dest="as_html")
    a = ap.parse_args(argv)
    from scripts.platformkit.frontend.feed_espn import EspnFreeFeed  # lazy
    feed = EspnFreeFeed()
    panel = build_clv_panel(a.sport) if a.clv else build_arb_panel(a.sport, feed)

    def _def(o: Any) -> Any:
        try:
            import numpy as _np  # noqa: PLC0415
            if isinstance(o, _np.floating): return float(o)
            if isinstance(o, _np.integer): return int(o)
        except ImportError:
            pass
        raise TypeError(type(o))

    if a.as_json:
        print(json.dumps(panel, indent=2, default=_def)); return 0
    if a.as_html and not a.clv:
        print(render_arb_html(panel)); return 0
    print(f"=== Money Panel: {panel.get('sport','?').upper()} ===")
    print(f"Status: {panel.get('status','?')} | edge_claimed: {panel.get('edge_claimed',False)}")
    if a.clv:
        print(f"CLV candidates: {panel.get('n_candidates', 0)}")
    else:
        print(f"Games: {panel.get('n_games',0)} | Multi-book: {panel.get('n_multibook_games',0)}")
        print(f"Arb: {len(panel.get('arbitrage',[]))} | Middles: {len(panel.get('middles',[]))}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
